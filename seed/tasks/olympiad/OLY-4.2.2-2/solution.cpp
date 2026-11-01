#include <bits/stdc++.h>
using namespace std;
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int n, k; cin >> n >> k;
    priority_queue<long long, vector<long long>, greater<long long>> top;
    for (int i = 0; i < n; ++i) {
        long long a; cin >> a;
        top.push(a);
        if ((int)top.size() > k) top.pop();
        cout << ((int)top.size() == k ? top.top() : -1) << "\n";
    }
}
