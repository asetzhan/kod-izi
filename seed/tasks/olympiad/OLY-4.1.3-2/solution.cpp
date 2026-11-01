#include <bits/stdc++.h>
using namespace std;
int main() {
    int n, W; cin >> n >> W;
    vector<long long> best(W + 1, 0);
    for (int i = 0; i < n; ++i) {
        int w; long long v; cin >> w >> v;
        for (int c = W; c >= w; --c) best[c] = max(best[c], best[c - w] + v);
    }
    cout << best[W] << "\n";
}
