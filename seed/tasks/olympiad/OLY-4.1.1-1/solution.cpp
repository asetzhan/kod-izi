#include <bits/stdc++.h>
using namespace std;
int main() {
    int n; long long k;
    cin >> n >> k;
    vector<long long> t(n);
    for (auto &x : t) cin >> x;
    long long lo = 0, hi = *min_element(t.begin(), t.end()) * k;
    while (lo < hi) {
        long long mid = lo + (hi - lo) / 2, made = 0;
        for (long long x : t) { made += mid / x; if (made >= k) break; }
        if (made >= k) hi = mid; else lo = mid + 1;
    }
    cout << lo << "\n";
}
