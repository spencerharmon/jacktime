import sys
import jack
import threading
from lib.jack.timebase_master import PyJackTimebaseMaster
from lib.jack.timebase_client import PyJackTimebaseClient
from lib.parser import args


def main(config):
    client = jack.Client(config['name'])
    shutdownevent = threading.Event()
    config['type'](client, shutdownevent)
    with client:
        try:
            shutdownevent.wait()
        except Exception as e:
            print(e.with_traceback(e.__traceback__))
            sys.exit(0)

if __name__ == "__main__":
    config = {}
    try:
        if args.master:
            config['name'] = 'jacktime_master'
            config['type'] = PyJackTimebaseMaster
    except AttributeError:
        pass
    try:
        if args.client:
            config['name'] = 'jacktime_client'
            config['type'] = PyJackTimebaseClient
    except AttributeError:
        pass
    main(config)