import bisect
from typing import List

def interp1(x, x0, x1, y0, y1):
    if x1 == x0:
        return y0
    t = (x - x0) / (x1 - x0)
    return y0 + (y1 - y0) * t

def locate(axis: List[float], x: float):
    if x <= axis[0]:
        return 0, 0, axis[0], axis[0]
    if x >= axis[-1]:
        j = len(axis)-1
        return j, j, axis[j], axis[j]
    i1 = bisect.bisect_right(axis, x)
    i0 = i1 - 1
    return i0, i1, axis[i0], axis[i1]

def bilinear(table, A_ft: float, T_c: float, ALT_COLS, TEMP_ROWS):
    r0, r1, T0, T1 = locate(TEMP_ROWS, T_c)
    c0, c1, A0, A1 = locate(ALT_COLS, A_ft/1000.0)

    Q11 = table[T0][c0]
    Q21 = table[T0][c1]
    Q12 = table[T1][c0]
    Q22 = table[T1][c1]

    if A1 == A0 and T1 == T0:
        return Q11

    if A1 == A0:
        return interp1(T_c, T0, T1, Q11, Q12)

    if T1 == T0:
        return interp1(A_ft/1000.0, A0, A1, Q11, Q21)

    fA_T0 = interp1(A_ft/1000.0, A0, A1, Q11, Q21)
    fA_T1 = interp1(A_ft/1000.0, A0, A1, Q12, Q22)
    return interp1(T_c, T0, T1, fA_T0, fA_T1)
