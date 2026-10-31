#include <iostream>
using namespace std;

int main() {
    int n;
    cin >> n;
    bool first = true;
    for (int d = 1; d <= n; ++d) {
        if (n % d == 0) {
            if (!first) cout << ' ';
            cout << d;
            first = false;
        }
    }
    cout << "\n";
    return 0;
}
