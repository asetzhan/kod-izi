#include <bits/stdc++.h>
using namespace std;
int main() {
    ios::sync_with_stdio(false); cin.tie(nullptr);
    int h, w; cin >> h >> w;
    vector<string> g(h);
    for (auto &row : g) cin >> row;
    vector<int> dist(h * w, -1);
    queue<int> q;
    for (int i = 0; i < h * w; ++i)
        if (g[i / w][i % w] == 'S') { dist[i] = 0; q.push(i); }
    int dr[] = {1, -1, 0, 0}, dc[] = {0, 0, 1, -1};
    while (!q.empty()) {
        int v = q.front(); q.pop();
        int r = v / w, c = v % w;
        if (g[r][c] == 'F') { cout << dist[v] << "\n"; return 0; }
        for (int d = 0; d < 4; ++d) {
            int nr = r + dr[d], nc = c + dc[d];
            if (nr < 0 || nr >= h || nc < 0 || nc >= w || g[nr][nc] == '#') continue;
            int u = nr * w + nc;
            if (dist[u] == -1) { dist[u] = dist[v] + 1; q.push(u); }
        }
    }
    cout << -1 << "\n";
}
