#include <bits/stdc++.h>
using namespace std;
vector<int> parent, sz;
int find(int x) { while (parent[x] != x) { parent[x] = parent[parent[x]]; x = parent[x]; } return x; }
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int n, m; cin >> n >> m;
    parent.resize(n + 1); sz.assign(n + 1, 1);
    iota(parent.begin(), parent.end(), 0);
    int comps = n;
    while (m--) {
        int a, b; cin >> a >> b;
        a = find(a); b = find(b);
        if (a != b) {
            if (sz[a] < sz[b]) swap(a, b);
            parent[b] = a; sz[a] += sz[b]; --comps;
        }
        cout << comps << "\n";
    }
}
