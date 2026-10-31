// Time limit for EXP-I-1: never finishes.
#include <iostream>
int main() {
    volatile unsigned long long x = 0;
    while (true) ++x;
}
