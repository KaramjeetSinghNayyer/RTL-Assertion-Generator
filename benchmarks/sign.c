/*@
  assigns \nothing;
  ensures (x > 0 ==> \result == 1) && (x < 0 ==> \result == -1) && (x == 0 ==> \result == 0);
*/
int sign(int x) {
    if (x > 0) return 1;
    if (x < 0) return -1;
    return 0;
}