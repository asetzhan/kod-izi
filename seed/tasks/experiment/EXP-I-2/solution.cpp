#include <iostream>
using namespace std;

int main() {
    long long a, b, c;
    cin >> a >> b >> c;
    long long best = a;
    if (b > best) best = b;
    if (c > best) best = c;
    cout << best << "\n";
    return 0;
}
