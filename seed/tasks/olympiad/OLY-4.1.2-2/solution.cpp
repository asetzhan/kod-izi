#include <bits/stdc++.h>
using namespace std;
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int q; cin >> q;
    while (q--) {
        long long a, m; unsigned long long b;
        cin >> a >> b >> m;
        long long r = 1 % m; a %= m;
        while (b) { if (b & 1) r = r * a % m; a = a * a % m; b >>= 1; }
        cout << r << "\n";
    }
}
