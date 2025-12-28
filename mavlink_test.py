from mavlinkHandler import MAVLinkHandlerDronekit as MAVLinkHandler
import time
mavlink_handler = MAVLinkHandler('10.42.0.2:14552')
print('vehicle have connected')
time.sleep(1)
#print('changing mode')
#print(mavlink_handler.get_location())
#mavlink_handler.set_parameter_value('WP_LOITER_RAD', 20)
#mavlink_handler.set_mode('GUIDED')
# print(mavlink_handler.simple_go_to(37.7749, -12.4194, 10))  # Example coordinates

approach_lat = 41.1004099
approach_lon = 28.5511681
start_altitude = 105

mavlink_handler.set_mode('MANUAL')
print(f'{mavlink_handler.get_location()}')
mavlink_handler.simple_go_to(approach_lat,approach_lon,start_altitude ,block=False, distance_radius=20)
