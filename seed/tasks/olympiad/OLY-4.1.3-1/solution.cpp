#include <bits/stdc++.h>
using namespace std;
int main() {
    const long long MOD = 1000000007;
    int n, k, b; cin >> n >> k >> b;
    vector<char> bad(n + 1, 0);
    for (int i = 0; i < b; ++i) { int x; cin >> x; bad[x] = 1; }
    vector<long long> dp(n + 1, 0);
    dp[0] = 1;
    long long window = 1;
    for (int i = 1; i <= n; ++i) {
        dp[i] = bad[i] ? 0 : window;
        window = (window + dp[i]) % MOD;
        if (i - k >= 0) window = (window - dp[i - k] + MOD) % MOD;
    }
    cout << dp[n] << "\n";
}
