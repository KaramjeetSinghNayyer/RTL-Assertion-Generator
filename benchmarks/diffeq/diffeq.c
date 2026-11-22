/*@
  requires dx > 0;
  requires a <= 2147483647 - dx;
  assigns \nothing;
  ensures x >= a ==> \result == y;
  ensures (x < a && a <= x + dx) ==> \result == y + u * dx;
*/
int diffeq(int x, int dx, int u, int a, int y) {
    /*@
      loop invariant \at(x, Pre) >= a ==> (x == \at(x, Pre) && y == \at(y, Pre));
      loop invariant \at(x, Pre) < a ==> \at(x, Pre) <= x < a + dx;
      loop invariant (\at(x, Pre) < a && a <= \at(x, Pre) + dx) ==>
          (x == \at(x, Pre) && y == \at(y, Pre) && u == \at(u, Pre)) ||
          (x == \at(x, Pre) + dx && y == \at(y, Pre) + \at(u, Pre) * dx);
      loop assigns x, y, u;
      loop variant a - x;
    */
    while (x < a) {
        int u1 = u - (3 * x * u * dx) - (3 * y * dx);
        int y1 = y + (u * dx);
        int x1 = x + dx;
        x = x1;
        y = y1;
        u = u1;
    }
    return y;
}
