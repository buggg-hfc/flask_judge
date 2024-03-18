#include <vector>

std::vector<std::vector<int>> v;
std::vector<int> t(10000, 1);

int main() {
    while (true) {
        v.push_back(t);
    }
    return 0;
}
