#include <bits/stdc++.h>
using namespace std;
int main() {
    const int N = 1000000;
    vector<char> composite(N + 1, 0);
    vector<int> pref(N + 1, 0);
    composite[0] = composite[1] = 1;
    for (int i = 2; (long long)i * i <= N; ++i)
        if (!composite[i])
            for (int j = i * i; j <= N; j += i) composite[j] = 1;
    for (int i = 1; i <= N; ++i) pref[i] = pref[i - 1] + !composite[i];
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int q; cin >> q;
    while (q--) { int l, r; cin >> l >> r; cout << pref[r] - pref[l - 1] << "\n"; }
}
