#include <iostream>
using namespace std;

int main() {
    int n;
    cin >> n;
    long long sum = 0;
    for (int i = 0; i < n; ++i) {
        long long x;
        cin >> x;
        if (x % 2 != 0) sum += x;
    }
    cout << sum << "\n";
    return 0;
}
