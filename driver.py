import logging
from logging.handlers import RotatingFileHandler
import sys
# import decoder as dec
# import decoder_temp as dec
import decoder as dec
import numpy as np
import threading
import time

import cv2



''' Function to set the general logging '''
def set_logger(terminal=False, file=False):
    handlers = []
    if file:
        handlers.append(RotatingFileHandler('frame_capture_temp.log',maxBytes=1000000,backupCount=20))
    if terminal:
        handlers.append(logging.StreamHandler(sys.stdout))

    if any((terminal, file)):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s:%(levelname)s:%(name)s:%(message)s',
            handlers=handlers)

set_logger(terminal=True,file=False)

decoder = dec.VidStreamClass_Test(Address='rtsp://wowzaec2demo.streamlock.net/vod/mp4:BigBuckBunny_115k.mp4',q1=1,gpu=True)
# decoder.SET_TF()
while True:
    image = decoder.get_frame()
    print(image[0].shape)
    cv2.imshow('w',image[0])
    k=cv2.waitKey(33)
    if k==27:
        break

