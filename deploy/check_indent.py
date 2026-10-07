with open(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src\paper\journal.py', 'r') as f:
    lines = f.readlines()
    line = lines[230]
    print('Length:', len(line))
    print('Repr:', repr(line))
    print('Char at 80:', repr(line[80]) if len(line) > 80 else 'N/A')
    for i, ch in enumerate(line):
        if ord(ch) > 127 or ch in '\t\r\f\v':
            print('  Pos', i, 'ord=', ord(ch), 'char=', repr(ch))