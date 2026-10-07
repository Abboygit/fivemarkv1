with open(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src\paper\journal.py', 'rb') as f:
    content = f.read()
    try:
        compile(content, 'journal.py', 'exec')
        print('Compile OK')
    except SyntaxError as e:
        print('SyntaxError:', e)
        print('Line:', e.lineno)
        print('Offset:', e.offset)
        print('Text:', e.text)
        # Show context around error
        lines = content.split(b'\n')
        start = max(0, e.lineno - 5)
        end = min(len(content.split(b'\n')), e.lineno + 5)
        for i in range(start, end):
            line = content.split(b'\n')[i]
            marker = '>>> ' if i + 1 == e.lineno else '    '
            print(f'{marker}{i+1:4d}: {line[:80]}')