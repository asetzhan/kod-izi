// Runtime error for EXP-I-1: division by zero.
#include <iostream>
int main() {
    long long n;
    std::cin >> n;
    volatile long long zero = 0;
    std::cout << n / zero << "\n";
}
