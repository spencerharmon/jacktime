import sys
import threading
import jack
from pprint import pprint


class TimebaseConfig(object):
    def __init__(self, pos):
        """

        :param client: python-jack Client object
        """
        self.usecs = pos.usecs
        self.frame_rate = pos.frame_rate
        self.frame = pos.frame
        #xor to keep active config.
        self.valid = pos.valid ^ jack._lib.JackPositionBBT
        if pos.valid & jack._lib.JackPositionBBT:
            self.bar = pos.bar
            self.beat = pos.beat
            self.tick = pos.tick
            self.bar_start_tick = pos.bar_start_tick
            self.beats_per_bar = pos.beats_per_bar
            self.beat_type = pos.beat_type
            self.ticks_per_beat = pos.ticks_per_beat
            self.beats_per_minute = pos.beats_per_minute
        else:
            self.bar = 0
            self.beat = 1
            self.tick = 0
            self.bar_start_tick = 0
            #default to 4/4
            self.beats_per_bar = 4
            self.beat_type = 4
            self.ticks_per_beat = 1920.0
            self.beats_per_minute = 120.0

    def getPos(self):
        pos = jack._ffi.new("jack_position_t *")
        pos.usecs = self.usecs
        pos.frame_rate = self.frame_rate
        pos.valid = self.valid
        pos.bar = self.bar
        pos.beat = self.beat
        pos.tick = self.tick
        pos.bar_start_tick = self.bar_start_tick
        pos.beats_per_bar = self.beats_per_bar
        pos.beat_type = self.beat_type
        pos.ticks_per_beat = self.ticks_per_beat
        pos.beats_per_minute = self.beats_per_minute
        return pos


class PyJackTimebaseMaster(object):
    def __init__(self, client, shutdownevent):
        """

                :param client: python-jack Client object
                :param shutdownevent: threading event to signal shutdown
        """
        self.client = client
        self.shutdownevent = shutdownevent

        state, pos = self.client.transport_query_struct()
        self.config = TimebaseConfig(pos)

        self.client.set_process_callback(self.process)
        self.client.set_shutdown_callback(self.shutdown)

        self.client.transport_reposition_struct(self.config.getPos())

    def set_timebase_callback(self):
        self.client.set_timebase_callback(callback=self.timebase_callback)

    def timebase_callback(self, state, blocksize, pos, new_pos):
        """
        TODO
        The goal of this timebase callback is to ensure that the bar and beat information is consistent
        on requests to modify the current jack timebase information, and to the extent possible, ensure
        that beats occur at regular intervals.
        Philosophically, the purpose of having timebase information at all is to ensure that clients
        with the need to synchronise to this data (i.e. play on beat) have enough information to do
        so.
        At present, clients have interpreted this data in disparate ways as well as failed to handle
        edge cases, leading to the inability to sync properly across software.
        A significant limitation of the current implementation is that clients don't have sufficient
        information about the exact frame on which they should perform their next quantized operation
        without performing some tricky math and maintaining state to correct timing errors.
        A formula (bpm/60)*samplerate (see set_frames_per_beat) should give something approximating
        the correct number of samples that should occur before the beat has changed. However, in
        practice, this figure cannot be relied on to predict the next beat frame.

        Below is some software I have reviewed for implementation-specific details about Jack timebase
        data:

        non-timeline: properly updates bar number and beat number, on reposition, but fails to update tick


        As in Jack..[put docs here]
        Question: is it possible to receive independent callbacks from multiple clients in one cycle?
        Also, is a 'cycle' when all clients have completed their process functions or when one
        client has completed its function, making all clients completing theirs, e.g. a round of cycles?
        Also, client process functions occur in sequence or parallel?
        :param state: Rolling, stopped, et c..
        :param blocksize: samples? in block
        :param pos: the struct with bbt info
        :param new_pos: bool. true if it's an instruction to move.
        :return: None
        """

        # pos is a cffi cdata object. pos[0] represents the
        # dereferenced value of the jack_position_t struct
        # pointed to by pos[0] (typically spelled *pos in C++)
        import time
        pos[0] = self.config.getPos()

    def process(self, nframes):
        self.state, self.pos = self.client.transport_query_struct()
        x, self.posd = self.client.transport_query()
        self.next_frame = self.pos.frame + nframes
        pprint(self.posd)
#        if self.state == jack.ROLLING:
#            self.increment_beat()

#        print(self.pos.beat)
#        pass
#        print(frames)
#        print(self.client.transport_query_struct())


    def increment_beat(self):
        pos = self.pos
#        print(self.next_frame)
#        pos.frame = self.next_frame / 2
        if pos.valid & jack._lib.JackPositionBBT:
            if pos.beat == self.pos.beats_per_bar:
                pos.beat = 1
                pos.bar += 1
            else:
                pos.beat += 1
            self.client.transport_reposition_struct(pos)

    def set_frames_per_beat(self):
        bps = self.config.beats_per_minute / 60
        fpb = bps * self.config.frame_rate
        self.fpb = fpb

    def new_config(self, pos):
        self.config = TimebaseConfig(pos)
        self.set_frames_per_beat()
    def shutdown(self):
        self.shutdownevent.set()


if __name__ == "__main__":
    client = jack.Client('jacktime')
    shutdownevent = threading.Event()
    PyJackTimebaseMaster(client, shutdownevent)
    with client:
        try:
            shutdownevent.wait()
        except Exception as e:
            print(e.with_traceback(e.__traceback__))
            sys.exit(0)
