/*@
  requires x > -2147483648;
  assigns \nothing;
  ensures \result >= 0;
  ensures (x >= 0 ==> \result == x) && (x < 0 ==> \result == -x);
*/
int abs(int x) {
    return (x < 0) ? -x : x;
}