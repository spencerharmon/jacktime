import argparse

parser = argparse.ArgumentParser(description='Monitor and control jack timebase parameters.')

subparser = parser.add_subparsers(
    title='Mode',
    dest='Mode',
    description="Choose mode 'client' or 'master'."
)

subparser.required = True

master = subparser.add_parser('master', help="For more info, try jacktime.py master -h")
mg = master.add_argument_group('Main')
mg.add_argument('master', action='store_true', help='Start jacktime in master mode.')


master.add_argument('--time-signature', '-t', )

client = subparser.add_parser('client', help="For more info, try jacktime.py client -h")
cg = client.add_argument_group('Main')
cg.add_argument('client', action='store_true', help='Start jacktime in client mode.')


args = parser.parse_args()