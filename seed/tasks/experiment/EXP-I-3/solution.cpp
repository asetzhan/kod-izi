#include <iostream>
using namespace std;

int main() {
    long long n;
    cin >> n;
    if (n == 0) {
        cout << 0 << "\n";
        return 0;
    }
    while (n > 0) {
        cout << n % 10;
        n /= 10;
    }
    cout << "\n";
    return 0;
}
