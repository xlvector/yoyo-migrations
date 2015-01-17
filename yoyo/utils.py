from __future__ import print_function
import sys

try:
    import termios

    def getch():
        """
        Read a single character without echoing to the console and without
        having to wait for a newline.
        """
        fd = sys.stdin.fileno()
        saved_attributes = termios.tcgetattr(fd)
        try:
            attributes = termios.tcgetattr(fd)  # get a fresh copy!
            attributes[3] = attributes[3] & ~(termios.ICANON | termios.ECHO)
            attributes[6][termios.VMIN] = 1
            attributes[6][termios.VTIME] = 0
            termios.tcsetattr(fd, termios.TCSANOW, attributes)

            a = sys.stdin.read(1)
        finally:
            # be sure to reset the attributes no matter what!
            termios.tcsetattr(fd, termios.TCSANOW, saved_attributes)
        return a

except ImportError:
    from msvcrt import getch


def prompt(prompt, options):
    """
    Display the given prompt and list of options and return the user selection.
    """

    while True:
        sys.stdout.write("%s [%s]: " % (prompt, options))
        sys.stdout.flush()
        ch = getch()
        if ch == '\n':
            ch = ([o.lower() for o in options if 'A' <= o <= 'Z'] +
                  list(options.lower()))[0]
        print(ch)
        if ch.lower() not in options.lower():
            print("Invalid response, please try again!")
        else:
            break

    return ch.lower()


def plural(quantity, one, plural):
    """
    >>> plural(1, '%d dead frog', '%d dead frogs')
    '1 dead frog'
    >>> plural(2, '%d dead frog', '%d dead frogs')
    '2 dead frogs'
    """
    if quantity == 1:
        return one.replace('%d', '%d' % quantity)
    return plural.replace('%d', '%d' % quantity)
