import cv2
import threading
import numpy as np


class Cap_Gstremer:
    def __init__(self):
        self.k=0
        image=np.zeros((300,300,3)).astype('uint8')
        self.Last=image.copy()
        A = threading.Thread(target=self.image_create)
        A.daemon = True
        A.start()
        self.cap = None
        self.frame_ready = threading.Event()


    def image_create(self):
        self.cap = cv2.VideoCapture('/home/ajith/Downloads/dance.mp4')
        while True:
            ret, image=self.cap.read()
            # image=np.zeros((300,300,3)).astype('uint8')
            cv2.putText(image, str(self.k), (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 1)
            self.k=self.k+1
            if ret:
                self.Last=image.copy()
                self.frame_ready.set()
            else:
                cv2.putText(image, str("Restarting"), (50, 50), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 0, 0), 1)
                self.cap.release()
                self.cap = cv2.VideoCapture('/home/ajith/Downloads/dance.mp4')
            #time.sleep(1/100)


    def isOpened(self):
        return True

    def get_canvas(self):
        A=self.Last
        return A


cam1 = Cap_Gstremer()

kk=1
cv2.namedWindow('A', cv2.WINDOW_NORMAL)
cv2.resizeWindow('A', 640, 360)
while True:
    # time.sleep(2)
    cam1.frame_ready.wait()
    image=cam1.Last.copy()
    cam1.frame_ready.clear()
    cv2.imshow('A',image)
    k=cv2.waitKey(1)
    if k==27:
       break
cv2.destroyAllWindows()

