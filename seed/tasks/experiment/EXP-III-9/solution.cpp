#include <algorithm>
#include <iostream>
#include <string>
using namespace std;

int main() {
    string s;
    cin >> s;
    if (next_permutation(s.begin(), s.end()))
        cout << s << "\n";
    else
        cout << -1 << "\n";
    return 0;
}
