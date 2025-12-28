from mavlinkHandler import MAVLinkHandlerDronekit as MAVLinkhandler

vehicle = MAVLinkhandler("127.0.0.1:14553")

safe = vehicle.get_location()[2]
while safe > 30:
    safe = vehicle.get_location()[2]
    print(f'Current altitude: {safe} m')    
    vehicle.set_target_attitude(roll=0, pitch=-50, yaw=0, thrust=0.2)

if safe <= 30:
    while safe <= 90:
        safe = vehicle.get_location()[2]
        print(f'Current altitude: {safe} m')
        vehicle.set_target_attitude(roll=0, pitch=40, yaw=0, thrust=1)
    
    