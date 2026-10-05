/*@
  requires x >= 0 && y >= 0;
  requires x + y <= 2147483647;
  assigns \nothing;
  ensures \result == x + y;
*/
int add(int x, int y) {
    return x + y;
}