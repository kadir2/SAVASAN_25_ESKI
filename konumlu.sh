#!/bin/bash

gnome-terminal --tab --title="Server" -- bash -c "cd /home/cello/SAVASAN_25/ && python server_son.py"

sleep 3

gnome-terminal --tab --title="Choose UAV" -- bash -c "cd /home/cello/SAVASAN_25/ && python choose_uav.py"

gnome-terminal --tab --title="Target Predictor" -- bash -c "cd /home/cello/SAVASAN_25/ && python target_predictor.py"

gnome-terminal --tab --title="Path Finder" -- bash -c "cd /home/cello/SAVASAN_25/ && python path.py"

