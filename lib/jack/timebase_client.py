import sys
import threading
import jack

class BeatStateMachine(object):
    """
    Estimates exact frame of beats based on recorded bar, beat, and frame information.

    Assumes that jack timebase master keeps frame-consistent beats since
    this is a basic requirement to play audio samples whose beat information
    is contained within the audio data along with events quantized to jack
    timebase, e.g. a recorded instrument playing along with a midi sequencer.

    Assumes that frames are used as discreet units of time as in their usage in ardour, 
    Assumes that frame consistency should always imply that frame number 0

    Given the available data, it is only possible to estimate beat intervals within the window
    of frames in the period provided to the process callback of the client implementing this
    class. The estimate can be refined over time as beats occur outside the projected beat
    frame and refine the beat width.

    Reports beat skew representing the percent difference between expected beat-width
    and observed beat-width. Skew results from the jack timebase master either changing
    beats at inconsistent frame intervals or changing beats at a different frame when
    replaying frames.

    Reports beat skew type:
        Linear: beat width increases with each beat
        Periodic: Beat occurs consistently late or early
        Bar: Beat occurs on unexpected bar.
    """
    def __init__(self, bpm, frame_rate, frames_per_period):
        #tuple representing the minimum and maximum possible beat widths given the recorded
        #beat frames.
        #Beat width unknown until second beat is recorded. Refined over time as beats are
        #recorded.
        self.beat_width = (0, 0)

        #see use in refine_beat_accuracy
        self.highest_recorded_beat = 0

        self.beats_per_bar = 1
        #beat map contains beat window information of each beat recorded or estimated
        #beat. windows are recalculated on request to project_next_beat as beat inaccuracy
        #narrows

        #seed first beat to beat_map
        bar = 1
        beat = 1
        beat_number = bar * self.beats_per_bar + beat
        beat_window = (0, frames_per_period)
        #Maximum inaccuracy is equal to frames_per_period*2 due to worst case of the first beat
        #occurring on the first frame of the period and the next beat occurring on the last frame
        #of its period.
        #Except in init function, inaccuracy should always be calculated by subtracting the minimum
        #beat width from the maximum beat width, i.e.:
        #min, max = self.beat_width
        #beat_inaccuracy = max-min
        beat_inaccuracy = frames_per_period * 2

        self.beat_map = {beat_number: {
                'beat_window': beat_window,
                'beat_inaccuracy': beat_inaccuracy
            }
        }

    def project_beat_frame(self, beat_number):
        """
        Return the projected beat frame for the beat specified.
        This is semantically relevant even in cases where the beat has been
        recorded since we can benefit from refinement using the current beat window.
        Used as an opportune time to back-fill beat window information with refined
        beat-width information by triggering refine_beat_accuracy.

        """
        try:
            # test if beat has been recorded
            x, y = self.beat_map[beat_number]

            # update accuracy if possible
            self.refine_beat_accuracy(beat_number)

            # load updated beat data
            min, max = self.beat_map[beat_number]

            # average the minimum and maximum beat frames.
            next_beat = min + max / 2
            return next_beat
        except AttributeError:
            # when self.beat_map[bar: [beat+1]] doesnt exist, estimate,
            # record, and return relevant information
            prev_min, prev_max = self.beat_map[beat_number]

            self.beat

            width_min, width_max = self.beat_width

            self.beat_map[beat_number + 1]



    def refine_beat_accuracy(self, beat_number):
        '''
        if necessary, check and recursively update beat window and beat inaccuracy information
        back to zero.
        :param bar: bar number specified for update
        :return: None
        '''
        #step through relevant beat backwards
        for i in reversed(range(beat_number, self.highest_recorded_beat)):
            for map_bar, map_beats in self.beat_map[i]:
                for map_beat in map_beats:
                    for map_beat_window, map_beat_inaccuracy in map_beat:
                        min, max = self.beat_width
                        current_beat_inaccuracy = max-min
                        if map_beat_inaccuracy > current_beat_inaccuracy:
                            #beat window is updated relative to the next-
                            #most-recent (presumably more accurate) beat
                            new_window = self.beat_map[i+1]['beat_window']





class PyJackTimebaseClient(object):
    def __init__(self, client, shutdownevent):
        """

                :param client: python-jack Client object
                :param shutdownevent: threading event to signal shutdown
        """
        self.client = client
        self.shutdownevent = shutdownevent

        state, pos = self.client.transport_query_struct()

        self.client.set_process_callback(self.process)
        self.client.set_shutdown_callback(self.shutdown)
        self.expected_next_frame = 0
        #keep state to signal discontinuity change only once
        self.o_discon = False

    def process(self, nframes):
        self.state, self.pos = self.client.transport_query_struct()
        for message in [m for m in [
            self.check_frame_number()
            ] if m is not None
        ]:
            #TODO: do something other than print
            print(message)

        if self.state is jack.ROLLING:
            self.expected_next_frame = self.pos.frame + nframes

    def check_frame_number(self):
        if self.pos.frame != self.expected_next_frame:
            if not self.o_discon:
                self.o_discon = True
                return "Transport frame position moved. New frame: {}".format(self.pos.frame)
        else:
            if self.o_discon:
                self.o_discon = False
                return None

    def check_beat_frame_consistency(self):


    def get_frames_per_beat(self):
        bps = self.pos.beats_per_minute / 60
        fpb = bps * self.pos.frame_rate
        self.fpb = fpb

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
