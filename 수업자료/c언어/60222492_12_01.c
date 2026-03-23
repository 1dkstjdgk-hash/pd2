#include <stdio.h>
#include <stdlib.h>
#include <time.h>

void main() {
	int dice;
	srand((unsigned)time(NULL));
	dice = 2 + (rand()%11);
	printf("두 개의 주사위의 합:%d",dice);
}

