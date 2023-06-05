import copy
import os
import queue
# import queue
from re import M
import warnings
import itertools
import threading
import sys
import logging
import gi
import numpy as np
import time
from enum import Enum
import multiprocessing as mp
import cv2
from multiprocessing.managers import SharedMemoryManager
from multiprocessing.shared_memory import SharedMemory
from logging.handlers import RotatingFileHandler
#import encoder as enc

# cython: language_level=3, boundscheck=False
gi.require_version('Gst', '1.0')
from gi.repository import Gst

Gst.init(None)

ACTIVE_DECODERS = dict()
DEFAULT_RESOLUTION = (1920, 1080)
DEFAULT_FPS = 30

MAXIMUM_FRAME_DUPLICATION_TIMEOUT = dict(timeout=5)
MAXIMUM_GET_FRAME_CALL_WAITING = 2000

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

#set_gst_logger(False,2)
set_logger(terminal=True, file=False)


def set_maximum_frame_duplication_timeout(timeout=5):
    global MAXIMUM_FRAME_DUPLICATION_TIMEOUT
    MAXIMUM_FRAME_DUPLICATION_TIMEOUT['timeout'] = timeout


def set_max_get_frame_call_wait(sec):
    global MAXIMUM_GET_FRAME_CALL_WAITING
    MAXIMUM_GET_FRAME_CALL_WAITING = sec
    return True


def on_debug(category, level, dfile, dfctn, dline, source, message, user_data):
    if source:
        logging.info('Debug {} {}'.format(
            Gst.DebugLevel.get_name(level), message.get()))
    else:
        logging.info('Debug {}: {}'.format(
            Gst.DebugLevel.get_name(level), message.get()))


def set_gst_logger(enable=False, verbosity=None):
    result = True
    try:
        if enable:
            Gst.debug_set_active(True)
            if verbosity and isinstance(verbosity, int) and (verbosity in range(0, 7)):
                Gst.debug_set_default_threshold(verbosity)
            else:
                result = False
                logging.error("GST verbosity allowed to be in 0-6")

            Gst.debug_add_log_function(on_debug, None)
            Gst.debug_remove_log_function(Gst.debug_log_default)

        else:
            Gst.debug_set_active(False)

        if result:
            enc.set_gst_logger(enable, verbosity)

    except Exception as e:
        result = False

    return result


# if not Gst.debug_is_active():
#     Gst.debug_set_active(True)
#     level = Gst.debug_get_default_threshold()
#     if level < Gst.DebugLevel.ERROR:
#         Gst.debug_set_default_threshold(Gst.DebugLevel.WARNING)
#     Gst.debug_add_log_function(on_debug, None)
#     Gst.debug_remove_log_function(Gst.debug_log_default)


warnings.filterwarnings("ignore")

'''Konwn issues
* if format changes at run time system hangs
'''


class StreamMode(Enum):
    INIT_STREAM = 1
    SETUP_STREAM = 1
    READ_STREAM = 2


class StreamCommands(Enum):
    FRAME = 1
    ERROR = 2
    HEARTBEAT = 3
    RESOLUTION = 4
    STOP = 5


class StreamCapture(mp.Process):

    def __init__(self, link, frame_memory, Dtype, resolution, framerate, Thermal=0, ID=0, TRES=640, gpu=False):
        """
        Initialize the stream capturing process
        link - rstp link of stream
        stop - to send commands to this process
        outPipe - this process can send commands outside
        """

        super().__init__()
        self.ID = ID
        self.streamLink = link
        self.Last_Frame = None
        self.Last_Time = time.time()
        self.gpu = gpu

        self.frame_memory = frame_memory
        self.Dtype = Dtype

        self.framerate = framerate
        # self.framerate = 30
        self.currentState = StreamMode.INIT_STREAM
        self.pipeline = None
        self.source = None
        self.decode = None
        self.convert = None
        self.sink = None
        self.image_arr = None
        self.newImage = False
        self.frame1 = None
        self.frame2 = None
        self.Thermal = Thermal
        self.TRES = TRES
        self.err = 0

        self.width = resolution[0] if resolution else None
        self.height = resolution[1] if resolution else None
        default_framerate = 30
        self.framerate = framerate if framerate else default_framerate

        self.new_frame_ready = mp.Event()
        self.stop = mp.Event()
        self.run_recovery = mp.Event()
        self.pause_event = mp.Event()
        self.resume_event = mp.Event()

    def pipeline_loop_job(self):

        if self.gpu:
            self.pipeline = Gst.parse_launch('rtspsrc name=m_rtspsrc !\
                rtph264depay ! queue ! nvdec ! \
                                appsink name=m_appsink')

            logging.info("GPU Decoding activated !")

        else:
            self.pipeline = Gst.parse_launch('rtspsrc name=m_rtspsrc ! \
                rtph264depay name=m_rtph264depay ! avdec_h264 name=m_avdech264 ! \
                    videoscale method=0 ! video/x-raw{} ! \
                        videoconvert name=m_videoconvert ! \
                            videorate name=m_videorate ! \
                                appsink name=m_appsink'.format(
                ',width=' + str(self.width) + ',height=' + str(self.height) if self.width and self.height else ''))

            logging.info("CPU Decoding activated !")

        # source params
        self.source = self.pipeline.get_by_name('m_rtspsrc')
        self.source.set_property('latency', 0)
        self.source.set_property('location', self.streamLink)
        self.source.set_property('protocols', 'tcp')
        self.source.set_property('retry', 100)
        self.source.set_property('timeout', 100)
        self.source.set_property('tcp-timeout', 5000000)
        self.source.set_property('drop-on-latency', 'true')

        # decode params
        # self.decode = self.pipeline.get_by_name('m_avdech264')
        # self.decode.set_property('max-threads', 2)
        # self.decode.set_property('output-corrupt', 'false')

        # convert params
        # self.convert = self.pipeline.get_by_name('m_videoconvert')

        # framerate parameters
        # self.framerate_ctr = self.pipeline.get_by_name('m_videorate')

        # self.framerate_ctr.set_property('max-rate', self.framerate / 1)
        # self.framerate_ctr.set_property('drop-only', 'true')

        # sink params
        self.sink = self.pipeline.get_by_name('m_appsink')

        # Maximum number of nanoseconds that a buffer can be late before it is dropped (-1 unlimited)
        # flags: readable, writable
        # Integer64. Range: -1 - 9223372036854775807 Default: -1
        self.sink.set_property('max-lateness', 500000000)

        # The maximum number of buffers to queue internally (0 = unlimited)
        # flags: readable, writable
        # Unsigned Integer. Range: 0 - 4294967295 Default: 0
        self.sink.set_property('max-buffers', 5)

        # Drop old buffers when the buffer queue is filled
        # flags: readable, writable
        # Boolean. Default: false
        self.sink.set_property('drop', 'true')

        # Emit new-preroll and new-sample signals
        # flags: readable, writable
        # Boolean. Default: false
        self.sink.set_property('emit-signals', True)

        # # sink.set_property('drop', True)
        # # sink.set_property('sync', False)

        # The allowed caps for the sink pad
        # flags: readable, writable
        # Caps (NULL)
        caps = Gst.caps_from_string(
            'video/x-raw, format=(string){BGR}')
        self.sink.set_property('caps', caps)

        # if not self.source or not self.sink or not self.pipeline or not self.decode or not self.convert:
        #     if PRINT_OUT == 1:
        #         logging.info("Not all elements could be created.")
        #     self.stop.set()

        self.sink.connect("new-sample", self.new_buffer, self.sink)
        logging.info("inside pipeline job")

        # Start playing
        self.pipeline.set_state(Gst.State.NULL)
        time.sleep(0.2)
        self.pipeline.set_state(Gst.State.READY)
        time.sleep(0.2)
        self.pipeline.set_state(Gst.State.PAUSED)
        ret = self.pipeline.set_state(Gst.State.PLAYING)
        logging.info('gstreamer pipeline started with return code:' + str(ret))
        self.bus = self.pipeline.get_bus()

        # trying to see if pipeline is set to playing state
        number_of_tries = 0
        while True:
            status, state, pending = self.pipeline.get_state(0)
            logging.info("number_of_tries:" + str(number_of_tries))
            if state == Gst.State.PAUSED:
                time.sleep(1)
                number_of_tries = number_of_tries + 1
                # logging.info(state)
            else:
                break
            if number_of_tries > 5:
                break

        # if ret == Gst.StateChangeReturn.FAILURE:
        #     logging.info("Unable to set the pipeline to the playing state.")
        #     self.stop.set()

        # Wait until error or EOS

        while True:
            if self.stop.is_set():
                logging.info('stop event is set')
                self.stop_capture()
                break
            if self.resume_event.is_set():
                print('resuming the video')
                self.resume_capture()
                print('resumed the video')
                self.resume_event.clear()

            if self.pause_event.is_set():
                print("pausing the video")
                self.pause_capture()
                print("paused the video")
                self.pause_event.clear()
            message = self.bus.timed_pop_filtered(10000, Gst.MessageType.ANY)

            time.sleep(0.02)
            if message:
                if message.type == Gst.MessageType.ERROR:
                    err, debug = message.parse_error()
                    logging.info("Error received from element %s: %s" % (
                        message.src.get_name(), err))
                    logging.info("Debugging information: %s" % debug)
                    logging.info("End-Of-Stream reached.")

                    self.err = 1
                    break
                elif message.type == Gst.MessageType.EOS:
                    logging.info("End-Of-Stream reached.")
                    self.err = 1
                    break
                elif message.type == Gst.MessageType.STATE_CHANGED:
                    if isinstance(message.src, Gst.Pipeline):
                        old_state, new_state, pending_state = message.parse_state_changed()
                        logging.info("Pipeline state changed from %s to %s." %
                                     (old_state.value_nick, new_state.value_nick))

        if not self.stop.is_set():
            logging.info("unexpected drop happened recovery will be run for ID : {}".format(self.ID))
            self.run_recovery.set()

    def resume_capture(self):
        self.pipeline.set_state(Gst.State.NULL)
        time.sleep(0.2)
        self.pipeline.set_state(Gst.State.READY)
        time.sleep(0.2)
        self.pipeline.set_state(Gst.State.PAUSED)
        ret = self.pipeline.set_state(Gst.State.PLAYING)

    def pause_capture(self):
        self.pipeline.set_state(Gst.State.PAUSED)
        time.sleep(0.1)
        self.pipeline.set_state(Gst.State.READY)
        time.sleep(0.1)

        self.pipeline.set_state(Gst.State.NULL)
        time.sleep(0.1)

    def stop_capture(self):
        self.stop.set()
        self.run_recovery.clear()
        self.pipeline.set_state(Gst.State.PAUSED)
        time.sleep(0.1)
        self.pipeline.set_state(Gst.State.READY)
        time.sleep(0.1)

        self.pipeline.set_state(Gst.State.NULL)
        time.sleep(0.1)

        self.pipeline.ref_count
        self.source.ref_count
        self.source.unref()
        self.pipeline.unref()
        # self.pipeline.remove(self.source)

        time.sleep(0.5)
        logging.info('Quit : {}'.format(self.ID))

    def soft_stop(self):
        self.pipeline.set_state(Gst.State.PAUSED)
        time.sleep(0.1)
        self.pipeline.set_state(Gst.State.READY)
        time.sleep(0.1)
        self.pipeline.set_state(Gst.State.NULL)
        time.sleep(0.1)

        # self.pipeline.ref_count
        # self.source.ref_count
        # self.source.unref()
        # self.pipeline.unref()
        # self.pipeline.remove(self.source)

        time.sleep(0.5)
        logging.info('Cleaning up pipeline for restarting for recovery for cam ID : {}'.format(self.ID))

    def gst_to_opencv(self, sample):
        buf = sample.get_buffer()
        caps = sample.get_caps()

        # Print Height, Width and Format
        # logging.info(caps.get_structure(0).get_value('format'))
        # logging.info(caps.get_structure(0).get_value('height'))
        # logging.info(caps.get_structure(0).get_value('width'))

        # Setting the resolution

        arr = np.ndarray(
            (caps.get_structure(0).get_value('height'),
             caps.get_structure(0).get_value('width'),
             3),
            buffer=buf.extract_dup(0, buf.get_size()),
            dtype=np.uint8)
        return arr

    def new_buffer(self, sink, _):
        sample = sink.emit("pull-sample")
        arr = self.gst_to_opencv(sample)
        arr_memory = np.frombuffer(self.frame_memory.buf, dtype=self.Dtype)
        arr_memory[:] = arr.flatten()
        self.new_frame_ready.set()
        return Gst.FlowReturn.OK

    def run(self):
        self.recover_decoder_thread = threading.Thread(target=self.recover_decoder)
        self.recover_decoder_thread.daemon = True
        self.recover_decoder_thread.start()
        self.pipeline_loop_job()
        self.recover_decoder_thread.join()
        # while True:
        #     print("Keeping the run")
        #     time.sleep(1)
        #     if self.stop.is_set():
        #         break

    def get_new_frame_ready(self):
        return self.new_frame_ready

    def get_stop_event(self):
        return self.stop

    def get_pause_event(self):
        return self.pause_event

    def get_resume_event(self):
        return self.resume_event

    def recover_decoder(self):
        no_of_tries = 0
        while True:
            no_of_tries += 1
            self.run_recovery.wait()
            logging.info("{} th cam link source is retrying to connect for the {} time".format(self.ID, no_of_tries))
            self.soft_stop()
            self.pipeline_loop_job()
            time.sleep(3)
            status, state, pending = self.pipeline.get_state(0)
            if self.new_frame_ready.is_set():
                self.run_recovery.clear()
                logging.info('print stopping recovery')
                # break
            if not self.stop.is_set():
                if self.run_recovery.is_set():
                    logging.info("Keep trying recovery... for {} : ".format(self.ID))
            else:
                logging.info("Ending recovery thread for {} :".format(self.ID))
                break

            time.sleep(10)

        logging.info("Terminating recovery thread... for ID : {}".format(self.ID))


class VidStreamClass_Test:
    def __init__(self, Address, q1, resolution=DEFAULT_RESOLUTION, fps=DEFAULT_FPS, buffersize=10, gpu=False):
        self.TF_ON=0
        # self.resolution = resolution if isinstance(resolution, tuple) and len(resolution) == 2 and all(isinstance(no, (int, float)) for no in resolution) else None
        if isinstance(resolution, tuple) and len(resolution) == 2 and all(
                isinstance(no, (int, float)) for no in resolution):
            self.resolution = resolution
        else:
            self.resolution = DEFAULT_RESOLUTION
            logging.warning('Resolution is not available or not in a valid format ; Default APPLIED!')

        # self.framerate = fps if isinstance(fps, (int, float)) else None
        if isinstance(fps, (int, float)):
            self.framerate = fps
        else:
            self.framerate = DEFAULT_FPS
            logging.warning('FPS is not available or not in a valid format ; Default APPLIED!')

        self.gpu = gpu
        self.buffersize = buffersize
        self.Cam_idx = q1
        self.Last_Frame = (np.zeros((self.resolution[1], self.resolution[0], 3)).astype(np.uint8),[], 0, time.time())
        self.Last_Frame[0][:] = 100
        self.empty_frame = cv2.putText(self.Last_Frame[0], "No Frames available, Retrying...", (400, 350),
                                       cv2.FONT_HERSHEY_SIMPLEX, 2,
                                       (0, 0, 255), 2)

        self.frame_counter = 0

        self.Time_of_Last_Frame = None
        self.frame_duplication_timeout = MAXIMUM_FRAME_DUPLICATION_TIMEOUT['timeout']
        # Current Cam
        self.camProcess = None
        self.camlink = Address
        self.pixel_array = np.zeros((self.resolution[1], self.resolution[0], 3)).astype(np.uint8)

        self.buffer = queue.Queue(maxsize=self.buffersize)
        self.init_frame_time = time.time()
        self.frames_sended = 0
        self.get_frame_call_timestamp = None

        self.terminate = 0
        self.Thermal = 1
        self.stop = None
        self.pause_event = None
        self.halt_event = mp.Event()

        # self.startMain()
        self.main_thread_stop_event = threading.Event()
        self.main_thread = threading.Thread(target=self.startMain)
        self.main_thread.daemon = True
        self.main_thread.start()

        time.sleep(3)

        self.loop_get_frame_thread_stop_event = threading.Event()

        self.frame_thread = threading.Thread(target=self.Loop_get_frame)
        self.frame_thread.daemon = True
        self.frame_thread.start()

        logging.info("Started recieving thread")

        self.old_frame = (np.zeros((self.resolution[1], self.resolution[0], 3)).astype(np.uint8), 0, None)

        self.timer_event = threading.Event()
        self.timer_thread = threading.Thread(target=self.timer)
        self.timer_thread.daemon = True
        self.timer_thread.start()

    def startMain(self):
        logging.info('startMain thread has STARTED...')
        self.Dtype = self.pixel_array.dtype
        with SharedMemoryManager() as smm:
            self.shared_memory = smm.SharedMemory(size=self.pixel_array.nbytes)

            self.camProcess = StreamCapture(self.camlink,
                                            self.shared_memory,
                                            self.Dtype,
                                            self.resolution,
                                            self.framerate,
                                            self.Thermal,
                                            ID=self.Cam_idx,
                                            gpu=self.gpu)
            self.camProcess.err = 0
            self.camProcess.daemon = True
            self.camProcess.start()
            self.stop = self.camProcess.get_stop_event()
            self.pause_event = self.camProcess.get_pause_event()
            logging.info('gstreamer pipe line thread started')

        while True:
            time.sleep(0.3)
            if self.terminate == 1:
                self.stop.set()

                time.sleep(0.1)
                # self.camProcess.terminate()
                # logging.info("cam_process terminated")

                break

            if self.get_frame_call_timestamp and (
                    (time.time() - self.get_frame_call_timestamp) > MAXIMUM_GET_FRAME_CALL_WAITING):
                logging.warning('Decoder has been unused more than {} sec'.format(MAXIMUM_GET_FRAME_CALL_WAITING))
                logging.info('Maximum idle time exceeded ! Automatically shutting down the decoder.')

                self.loop_get_frame_thread_stop_event.set()
                self.terminate = 0
                self.stop.set()
                self.main_thread_stop_event.set()
                time.sleep(3)

                # to free the buffer to finish already waiting frame. inorder to complete the iteration and join the frame_thread
                if not self.buffer.empty():
                    _ = self.buffer.get()

                self.frame_thread.join()
                logging.info("Frame thread has joined ...")

                self.timer_thread.join()
                logging.info("Timer thread has joined ...")

                self.camProcess.join(3)
                logging.info("Camprocess has joined ...")
                self.camProcess.terminate()
                logging.info("Camprocess has terminated")

                break

        logging.info('Finished start Main')

    def get_canvas(self):
        frame = self.Last_Frame.copy()
        return frame

    def isOpened(self):
        return True
    def SET_TF(self):
        import tensorflow as tf
        self.tf=tf
        self.TF_ON=1
        return True

    def Loop_get_frame(self):
        mp_new_frame_ready_event = self.camProcess.get_new_frame_ready()
        frame = self.empty_frame
        f_counter = 0
        f_time = None
        self.frame_counter = 0
        while self.terminate == 0:
            if self.halt_event.is_set():
                frame = self.empty_frame
                f_counter = 0
                f_time = None
            else:
                frame_available = mp_new_frame_ready_event.wait(timeout=self.frame_duplication_timeout)
                if frame_available:
                    val = np.frombuffer(self.shared_memory.buf, dtype=self.Dtype)
                    frame = val.reshape(self.resolution[1], self.resolution[0], 3)
                    self.Time_of_Last_Frame = time.ctime()
                    self.Computer_Time_of_Last_Frame = time.time()
                    self.Camera_Stuck = 0
                    mp_new_frame_ready_event.clear()
                    self.frame_counter += 1
                    f_counter = self.frame_counter
                    f_time = self.Time_of_Last_Frame
                else:
                    frame = self.empty_frame
                    f_counter = 0
                    f_time = None
            frame=frame.astype('float32')

            if self.TF_ON==1:
                #print('WITH TF')
                self.Last_Frame = (frame,self.tf.identity(frame), f_counter, f_time)
                #self.Last_Frame = (frame, [], f_counter, f_time)

            else:
                print('NO TF')
                self.Last_Frame = (frame, [], f_counter, f_time)
            if not self.loop_get_frame_thread_stop_event.is_set():
                self.buffer.put(self.Last_Frame)
                # try:
                #     self.buffer.put(self.Last_Frame, block=False)
                # except Exception as e:
                #     print("Exception")
                #     print(e)
                #     temp = self.buffer.get()
                #     self.buffer.put(self.Last_Frame)
            else:
                break
        X=1+11

    def get_frame(self):
        self.get_frame_call_timestamp = time.time()
        if self.main_thread_stop_event.is_set():
            return (None, None, None,None)

        while (not self.buffer.full() and (not self.loop_get_frame_thread_stop_event.is_set())):
            #print("qsize=",self.buffer.qsize())
            time.sleep(0.003)

        try:
            new_frame = self.buffer.get(block=False)
        except:
            time.sleep(.01)
            #print('Waiting to get &^^&^ frame Buffer')
            new_frame = self.buffer.get()
        self.timer_event.wait()
        frame = self.old_frame
        self.old_frame = new_frame
        self.timer_event.clear()
        return frame

    def timer(self):
        while True:
            if self.loop_get_frame_thread_stop_event.is_set():
                break
            time.sleep(1 / self.framerate)
            self.timer_event.set()

    def canvas_getter(self):
        frame = self.Last_Frame
        return frame

    def canvas_setter(self, frame):
        cv2.rectangle(frame[0], (800, 200), (1200, 800), (0, 0, 255),
                      5)  # canvas_setter is not even needed if we use reference
        return True

    def get_status(self):
        return int(not self.terminate), *(self.resolution), self.framerate, self.camlink

    def shutdown(self):
        self.terminate = 1
        self.stop.set()
        self.loop_get_frame_thread_stop_event.set()
        self.main_thread_stop_event.set()
        time.sleep(1 / 2)
        logging.info("waiting for threads to close")
        self.main_thread.join()
        logging.info("Main thread has joined")
        time.sleep(1 / 2)
        self.timer_thread.join()
        logging.info("Timer thread has joined")

        if not self.buffer.empty():
            _=self.buffer.get()
        self.frame_thread.join()
        logging.info("Frame thread has joined")

        self.camProcess.join(3)
        logging.info("Camprocess has joined")
        self.camProcess.terminate()
        logging.info("Camprocess has terminated")
        # the method blocks until the process whose join() method is called terminates. If timeout is a positive number, it blocks at most timeout seconds. Note that the method returns None if its process terminates or if the method times out. Check the process’s exitcode to determine if it terminated.

        logging.info("Multiprocessing terminated from main process...")

    def resume(self):
        ret_val = True
        try:
            self.frame_duplication_timeout = MAXIMUM_FRAME_DUPLICATION_TIMEOUT['timeout']
            resume_event = self.camProcess.get_resume_event()
            resume_event.set()
            self.halt_event.clear()
        except Exception as e:
            logging.error("Error while running resume function : {}".format(e), exc_info=True)
            ret_val = False
        return ret_val

    def pause(self):
        ret_val = True
        try:
            self.frame_duplication_timeout = 0.001
            self.halt_event.set()
            self.pause_event = self.camProcess.get_pause_event()
            self.pause_event.set()
        except Exception as e:
            logging.error("Error while running resume function : {}".format(e), exc_info=True)
            ret_val = False
        return ret_val

    # def get_latest_frame(self):
    #     cmd, frame = self.get_frame()
    #     status = 'N/A'
    #     if str(cmd) == '0' or frame != np.zeros((self.resolution, 640, 3)):
    #          status = 'OK'
    #     return [frame, self.Time_of_Last_Frame, status]

    def __repr__(self):
        status_repr = {0: 'LIVE', 1: 'STOPED'}

        return '[({}) [{}] : {} , Last frame on :{}]'.format(
            self.Cam_idx,
            status_repr[self.terminate],
            self.camlink,
            self.Time_of_Last_Frame if self.Time_of_Last_Frame else 'N/A'
        )


''' For online media player properties'''


class Media_player:
    inc_id_object = itertools.count()

    def __init__(self, url, resolution, fps):
        self.url = url
        self.resolution = resolution
        self.fps = fps
        self.media_id = next(Media_player.inc_id_object)
        self.thread_obj = None
        self.thread_obj = VidStreamClass_Test(self.url, self.media_id, self.resolution, self.fps)
        self.add_to_active_decoders()

    def add_to_active_decoders(self):
        ACTIVE_DECODERS[self.media_id] = self

    def get_media(self):
        if self.thread_obj:
            return self.thread_obj


''' For decoding the local media file'''


class Offline_media_player:
    def __init__(self, path=None):
        if path and os.path.isfile(path):
            self.location = path
            self.cap = cv2.VideoCapture(self.location)
            self.frame_count = 0
            frame = np.zeros((300, 300, 3)).astype('uint8')
            self.last_frame = frame.copy()
            self.video_thread = threading.Thread(target=self.image_create)
            self.video_thread.daemon = True
            self.video_thread.start()

    def image_create(self):
        while (self.cap.isOpened()):
            ret, frame = self.cap.read()
            cv2.putText(frame, str(self.frame_count), (200, 200), cv2.FONT_HERSHEY_SIMPLEX, 5, (0, 0, 255), 10)
            self.frame_count = self.frame_count + 1
            if frame is not None:
                self.last_frame = frame.copy()
        else:
            self.cap.release()

    def isOpened(self):
        return True

    def get_canvas(self):
        if self.cap.isOpened():
            return self.last_frame

    def set_canvas(self, frame):
        self.last_frame = frame
        return True

    def get_frame(self):
        if self.cap.isOpened():
            return True, self.last_frame

    def get_media(self):
        return self
