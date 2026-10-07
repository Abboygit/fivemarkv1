with open(r'C:\Users\MY PC\Documents\Default Project\Five mark v1\deploy\src\paper\journal.py', 'rb') as f:
    content = f.read()
    lines = content.split(b'\n')
    print('Total lines:', len(lines))
    line = lines[230]
    print('Line 231:', repr(line))
    print('Length:', len(line))
    print('Hex:', ' '.join(hex(b) for b in line))
    print('Ends with:', repr(line[-10:]))
    # Check for tabs in indentation
    leading = line[:len(line) - len(line.lstrip())]
    if b'\t' in leading:
        print('TAB in indentation!')
    print('Leading bytes:', ' '.join(hex(b) for b in leading))
    print('Leading length:', len(leading))