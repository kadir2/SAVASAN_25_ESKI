#!/usr/bin/env pythimport cv2
from ultralytics import YOLO
from ultralytics.utils.plotting import Annotator 
from pyzbar.pyzbar import decode
import numpy as np
import redis
import struct
import cv2
import time
import os
import logging
import datetime
import shutil
import threading


class Logger:
    def init_logger(self):
        # Customcustom logger in order to log to both console and file
        self.logger = logging.Logger('GOAT - Kamikaze-Cam')
        # Set the log level
        self.logger.setLevel(logging.DEBUG)
        # Create handlers
        c_handler = logging.StreamHandler()
        
        log_file_path = 'GOAT_kamikaze_cam.log'
        old_logs_dir = "old_logs_kamikaze"
        
        if not os.path.exists(old_logs_dir):
            os.makedirs(old_logs_dir)
            
        if os.path.exists(log_file_path):
            # Generate a unique name for the log file in the old logs directory
            timestamp = datetime.datetime.now()
            new_log_file_name = f"GOAT_kamikaze_cam_{timestamp}.log"
            new_log_file_path = os.path.join(old_logs_dir, new_log_file_name)
            # Move the log file to the old logs directory
            shutil.move(log_file_path, new_log_file_path)
            
        f_handler = logging.FileHandler(log_file_path)
        # Set levels for handlers
        c_handler.setLevel(logging.ERROR)
        f_handler.setLevel(logging.DEBUG)

        # Create formatters and add it to handlers
        c_format = logging.Formatter('%(name)s - %(levelname)s - %(message)s')
        f_format = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        c_handler.setFormatter(c_format)
        f_handler.setFormatter(f_format)

        # Add handlers to the self.logger
        self.logger.addHandler(c_handler)
        self.logger.addHandler(f_handler)


class ImageProcessor(Logger):
    def __init__(self):
        self.init_logger()
        self.count = 0
        self.logger.debug('Loading model')
        self.model = YOLO('QR.pt')
        self.logger.debug('Model loaded')
        self.r = redis.Redis(host='localhost', port=6379, db=0)
        self.p = self.r.pubsub()
        self.counter = 0
        self.run_active = True
        
        self.r.set('didRead', 'False')
        self.r.set('qr_data', "")

        threading.Thread(target=self.redis_listener).start()

    def redis_listener(self):
        while True:
            time.sleep(0.4)
            message = self.r.get('kamikaze_buton').decode('utf-8')  # Redis'ten 'command' adında bir mesaj bekle
            # print('kamikaze_buton:',message)
            if message:
                command = message
                # print('command:',command)
                if command == 'True':
                    print('Kamikaze Buton Aktif')
                    self.run_active = True
                elif command == 'False':
                    # print('Kamikaze Buton Aktif Değil')
                    self.run_active = False
                    

    def fromRedis(self, n):
        """Retrieve Numpy array from Redis key 'n'"""
        encoded = self.r.get(n)
        if encoded is None:
            return None
        frame = self.convert_to_frame(encoded)
        self.logger.debug('Frame retrieved from Redis')
        return frame

    def textFromRedis(self,n):
        encoded = self.r.get(n)
        return encoded

    def convert_to_frame(self,frame_data):
        h, w = struct.unpack('>II',frame_data[:8])
        frame = np.frombuffer(frame_data, dtype=np.uint8, offset=8).reshape(h,w,3).copy()
        self.logger.debug('Frame converted to numpy array')
        return frame        

    def preprocess_image(self, image):
        resized_image = cv2.resize(image, (800, 600))  # Gereken çözünürlük
        gray_image = cv2.cvtColor(resized_image, cv2.COLOR_BGR2GRAY)
        self.logger.debug('Image preprocessed')
        return gray_image

    def read_qr_and_print(self, frame):
        #frame = cv2.imread(image_path)
        #processed_image = self.preprocess_image(frame)
        decoded_objects = decode(frame)

        if decoded_objects:
            for obj in decoded_objects:
                data = obj.data.decode("utf-8")
                self.logger.debug('Data: %s', data)
                self.r.set('didRead', 'True')
                break
        else:
            self.logger.debug('QR Code not found')
            self.r.set('didRead', 'False')

    def image_callback(self, frame):
        if self.counter == 0:
            results = self.model.predict(frame, conf=0.5)
            for r in results:
                annotator = Annotator(frame)
                boxes = r.boxes
                if boxes is not None :
                    for box in boxes:
                        b = box.xyxy[0]  # get box coordinates in (top 0, left 1, bottom 2, right 3) format
                        c = box.cls
                        annotator.box_label(b, self.model.names[int(c)])
                        self.logger.debug('Box: %s', b)

                        mask_img = annotator.result()
                        
                        crop_img = mask_img[int(b[1]//1.2):int(b[3]*1.2), int(b[0]//1.2):int(b[2]*1.2)]
                        #crop_img = mask_img[int(b[1]):int(b[3]), int(b[0]):int(b[2])]
                        if os.path.exists(f'detecteds') == False:
                            os.mkdir(f'detecteds')

                        cv2.imwrite(f'detecteds/image_{self.count}.png', crop_img)

                        decoded_objects = decode(crop_img)
                        if decoded_objects :
                            self.counter += 1
                            for obj in decoded_objects:
                                data = obj.data.decode("utf-8")
                                self.logger.debug('Data: %s', data)
                                #write file data
                                with open('data.txt', 'w') as f:
                                    f.write(data)
                                self.r.set('didRead', 'True')
                                self.r.set('qr_data', data)
                                # break
                        else:
                            self.logger.debug('QR Code not found')
                            self.r.set('didRead', 'False')
                                
                        self.count += 1

                else:
                    print("No boxes found")
                    self.r.set('didRead', 'False')
    

    def run(self):
        self.p.subscribe('frame')
        frame = self.fromRedis('frame')
        self.image_callback(frame)
        
        while True:
            time.sleep(0.05)
            if self.run_active == False:
                continue
            frame = self.fromRedis('frame')
            self.image_callback(frame)
            cv2.imshow('image', frame)
            cv2.waitKey(1)
        print('thread bitti')


if __name__ == '__main__':
    processor = ImageProcessor()

    processor.run()
        