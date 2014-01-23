import argparse
import inspect

import amulet


def setup_parser():
    parser = argparse.ArgumentParser(prog='amulet')
    subparsers = parser.add_subparsers(help='sub-command help')

    for name, obj in inspect.getmembers(amulet):
        if inspect.ismodule(obj):
            for baby_name, baby_obj in inspect.getmembers(obj):
                if baby_name == 'setup_parser':
                    getattr(obj, baby_name)(subparsers)

    return parser


def main():
    p = setup_parser()
    args = p.parse_args()
    args.func(args)

if __name__ == '__main__':
    main()
