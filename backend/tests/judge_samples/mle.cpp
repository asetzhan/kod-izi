// Memory limit for EXP-I-1: touches 1 GB, more than the 256 MB limit.
#include <iostream>
#include <vector>
int main() {
    std::vector<char> big(1024u * 1024u * 1024u, 1);
    std::cout << static_cast<int>(big[12345]) << "\n";
}
