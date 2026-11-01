import sys

from rectangle import area, perimeter


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit('usage: rectangle.pyz LENGTH WIDTH')
    length, width = float(sys.argv[1]), float(sys.argv[2])
    print(f'area={area(length, width)} perimeter={perimeter(length, width)}')


if __name__ == '__main__':
    main()
