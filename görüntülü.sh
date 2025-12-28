#!/bin/bash

gnome-terminal --tab --title="Frame Publisher" -- bash -c "cd /home/cello/SAVASAN_25/ && python frame_publisher.py; exec bash"

gnome-terminal --tab --title="Tespit" -- bash -c "cd /home/cello/SAVASAN_25/ && python detection.py; exec bash"

sleep 3

gnome-terminal --tab --title="Tracker" -- bash -c "cd /home/cello/SAVASAN_25/ && python tracker.py; exec bash"

sleep 3

gnome-terminal --tab --title="Tracker" -- bash -c "cd /home/cello/SAVASAN_25/ && python GOAT_guidance.py; exec bash"

