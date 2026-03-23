#include <stdio.h>
void f();
int i;
void main() {
for(i = 0;i < 5; i++)
{
f();
}
}
void f() {
for(i = 0;i < 10; i++)
printf("#");
}

