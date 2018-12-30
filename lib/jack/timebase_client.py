import sys
import threading
import jack
from pprint import pprint

class BeatStateMachine(object):
    """
    Estimates frame on which beats occur based on recorded bar, beat, and frame information.

    Assumes that jack timebase master keeps frame-consistent beats since
    this is a basic requirement to play audio samples whose beat information
    is contained within the audio data along with events quantized to jack
    timebase, e.g. a recorded instrument playing along with a midi sequencer.

    Assumes that frames are used as discreet units of time as in their usage in ardour,
    non-daw, openav luppp, sooperlooper, et al.

    Assumes that frame consistency should always imply that frame number 0 is the first frame of
    bar 1 beat 1.

    Assumes that beats should always be equivalent in duration.

    Does not support the changing of time signature or samplerate. This is an unfortunate side
    effect of the current implementation of Jack timebase, since there is insufficient information
    to predict changes of this kind. This can probably be fixed.

    Can only estimate beat frames accurate to within the number of frames provided to the process
    callback. The estimate can be refined over time as beats occur outside the projected beat
    frame and refine the beat width. This process is fairly computationally expensive.

    Reports beat skew representing the percent difference between expected beat-width
    and observed beat-width. Skew results from the jack timebase master either changing
    beats at inconsistent frame intervals or changing beats at a different frame when
    replaying frames.

    Reports beat skew type:
        Linear: beat width increases with each beat
        Periodic: Beat occurs consistently late or early
        Bar: Beat occurs on unexpected bar.
    """
    def __init__(self, pos, max_buffer_size):
        self._max_buffer_size = max_buffer_size
        # tuple representing the minimum and maximum possible frames for a beat given the recorded
        # beat frames.
        # Beat width initialized with estimate from bpm until second beat is recorded. Refined
        # over time as beats are recorded.
        # Estimate is fpb conversion +/- 1/2 max buffer.
        fpb = self.get_frames_per_beat(pos)
        fmin = int(fpb - self._max_buffer_size)
        fmax = int(fpb + self._max_buffer_size)
        fpb_range = (fmin, fmax)

        # disable multiple checking of beat frames against adjusted fpb.
        self.multi_check_disable = False
        self.fpb_group = {0: {'fpb': fpb_range,
                              'start_beat': 1,
                              'end_beat': None}}

        self.current_fpb_group = 0

        #beat map contains beat window information of each beat recorded or estimated
        #beat. windows are recalculated on request to project_next_beat as beat inaccuracy
        #narrows

        #seed first beat to beat_mapexact

        beat_number = 1
        beat_window = (0, self._max_buffer_size)

        #fpb group is
        self.beat_map = {beat_number:
            {
            'beat_window': beat_window,
            'fpb_group': 0,
            'checked': False
            }
        }

        #register current beat (since it's not always bar 1 beat 1)
        cur_beat_no = (pos.bar - 1) * pos.beats_per_bar + pos.beat
        self.record_beat(pos, self._max_buffer_size)

    def record_beat(self, pos, nframes):
        """
        Signals position at time of detected beat change.
        This is a good time also to detect opportunities to shrink the fpb
        window for more accurate beat predictions.
        Do not register beat when transport is moved. This will lead to unexpected
        behavior.
        :param pos: cdata object, jack_position_t C struct, via jack-python
        :return: None
        """
        beat_number = self.beat_number_from_pos(pos)
        self.beat_map[beat_number] = {'beat_window': (pos.frame, pos.frame + nframes),
                                    'fpb_group': self.current_fpb_group,
                                      'checked': False}

        self.adjust_fpb_range()

    def adjust_fpb_range(self):
        first, second = self.fpb_group[self.current_fpb_group]['fpb']
        low = first
        high = second
        if first > second:
            high = first
            low = second
        start_beat = self.fpb_group[self.current_fpb_group]['start_beat']
        end_beat = self.fpb_group[self.current_fpb_group]['end_beat']

        if end_beat is not None:
            for beat in range(start_beat, end_beat):
                if beat > start_beat:
                    beat_start_frame, beat_end_frame = self.beat_map[beat]['beat_window']
                    too_low = True
                    while too_low:
                        if low * beat < beat_start_frame:
                            low += 1
                        else:
                            too_low = False
                    too_high = True
                    while too_high:
                        if high * beat > beat_end_frame:
                            high -=1
                        else:
                            too_high = False
        else:
            for beat in self.beat_map:
                if not self.beat_map[beat]['checked']:
                    beat_start_frame, beat_end_frame = self.beat_map[beat]['beat_window']
                    if beat > 1:
                        too_low = True
                        while too_low:
                            min_frames = low * (beat - 1)
                            if min_frames < beat_start_frame:
                                low += 1
                            else:
                                too_low = False
                        too_high = True
                        while too_high:
                            max_frames = high * (beat - 1)
                            if max_frames > beat_end_frame:
                                high -= 1
                            else:
                                too_high = False
                    if self.multi_check_disable:
                        self.beat_map[beat]['checked'] = True

        self.fpb_group[self.current_fpb_group]['fpb'] = (low, high)



    def record_bpm_change(self, pos):
        #mark end of previous group
        current_beat = self.beat_number_from_pos(pos)
        self.fpb_group[self.current_fpb_group]['end_beat'] = current_beat

        #log next fpb group
        self.current_fpb_group += 1
        fmin = int(self.get_frames_per_beat(pos) - self._max_buffer_size)
        fmax = int(fmin + (self._max_buffer_size * 2))
        fpb = (fmin, fmax)
        self.fpb_group[self.current_fpb_group] = {'fpb': fpb,
                              'start_beat': current_beat + 1,
                              'end_beat': None}

    def predict_beat_frame(self, beat_number):
        """
        Return the projected beat frame for the beat specified.
        This is semantically relevant even in cases where the beat has been
        recorded since we can benefit from refinement using the current beat window.
        Used as an opportune time to back-fill beat window information with refined
        beat-width information by triggering refine_beat_accuracy.

        """
        if beat_number > 0:
            # get fpb range from group
            group = self.current_fpb_group
            try:
                group = self.beat_map[beat_number]['fpb_group']
            except KeyError:
                pass
            fpb_range = self.fpb_group[group]['fpb']

            # determine the frame at which this tempo started:
            start_beat = self.fpb_group[group]['start_beat']
            l, h = self.beat_map[start_beat]['beat_window']
            start_frame = (l + h) / 2

            # get beat count from fpb group
            beat_count = beat_number - start_beat

            # average fpb range
            low, high = fpb_range
            fpb = (low + high) / 2

            # frame = fpb * beat_count + start_frame
            # y = mx+b
            return (fpb * beat_count) + start_frame

    def get_frames_per_beat(self, pos):
        bps = pos.beats_per_minute / 60
        fpb = pos.frame_rate / bps
        return fpb

    def beat_number_from_pos(self, pos):
        """
        returns the current absolute beat number
        :param pos: cdata object, jack_position_t C struct, via jack-python
        :return:
        """
        return int((pos.bar - 1) * pos.beats_per_bar + pos.beat)

    def reposition(self, pos):
        beat_number = self.beat_number_from_pos(pos)
        for group_number in self.fpb_group:
            group_info = self.fpb_group[group_number]
            if beat_number > group_info['start_beat']:
                if group_info['end_beat'] is None:
                    self.current_fpb_group = group_number
                elif beat_number < group_info['end_beat']:
                    self.current_fpb_group = group_number


    def set_max_buffer_size(self, max_buffer_size):
        """
        Accessor function to change self._max_buffer_size.
        :param max_buffer_size: The maximum number of frames that can be passed to the
        process callback function.
        :return: None
        """
        #todo: does this accessor need to exist?
        #maybe it would be useful if we decide to keep track of tempo change consistency
        #in the beat map. We could re-initialize the beat width on bpm change and refine beat
        #frames for the tempo "block" TODO
        self._max_buffer_size = max_buffer_size


class PyJackTimebaseClient(object):
    def __init__(self, client, shutdownevent):
        """

                :param client: python-jack Client object
                :param shutdownevent: threading event to signal shutdown
        """
        self.client = client
        self.shutdownevent = shutdownevent

        self.state, self.pos = self.client.transport_query_struct()

        self.beat_state = BeatStateMachine(self.pos, self.client.blocksize)

        self.client.set_process_callback(self.process)
        self.client.set_shutdown_callback(self.shutdown)
        #this is named set_buffer_size_callback in jack.
        self.client.set_blocksize_callback(self.buffer_size_callback)
        self.expected_next_frame = 0
        #keep state to signal discontinuity change only once
        self.o_discon = False

        self.beat_last_cycle = 0

    def process(self, nframes):
        self.state, self.pos = self.client.transport_query_struct()

        if self.check_if_repositioned():
            self.beat_state.reposition(self.pos)
        elif self.pos.beat != self.beat_last_cycle:
            self.beat_state.record_beat(self.pos, nframes)

        print(self.beat_state.predict_beat_frame(self.beat_state.beat_number_from_pos(self.pos) + 1))
        print(self.beat_state.fpb_group)

        self.after_process(nframes)

    def after_process(self, nframes):
        self.beat_last_cycle = self.pos.beat

        if self.state is jack.ROLLING:
            self.expected_next_frame = self.pos.frame + nframes
        else:
            self.expected_next_frame = self.pos.frame

    def check_if_repositioned(self):
        """
        Only valid during process callback.
        :return: bool
        """
        if self.pos.frame != self.expected_next_frame:
            if not self.o_discon:
                self.o_discon = True
                return True
        else:
            if self.o_discon:
                self.o_discon = False
                return False

    def buffer_size_callback(self, bufsize):
        #inform beat state machine of the change.
        self.beat_state.set_max_buffer_size(bufsize)

    def shutdown(self):
        self.shutdownevent.set()


if __name__ == "__main__":
    client = jack.Client('jacktime')
    shutdownevent = threading.Event()
    tclient = PyJackTimebaseClient(client, shutdownevent)
    with client:
        try:
            shutdownevent.wait()

        except KeyboardInterrupt:
            pprint(tclient.beat_state.beat_map)
        except Exception as e:
            print(e.with_traceback(e.__traceback__))
            sys.exit(0)
