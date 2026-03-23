#include <stdio.h>
#include <stdlib.h>
#include <time.h>

void main() {
	int rn;
	srand((unsigned)time(NULL));
	rn = (rand()%100)+1;
	if(rn <= 5)
		printf("1등 상품에 당첨 되셨습니다!");
	else if(rn <= 20)
		printf("2등 상품에 당첨 되셨습니다!");
	else if(rn <= 50)
		printf("3등 상품에 당첨 되셨습니다!");
	else
		printf("4등 상품에 당첨 되셨습니다!");
}
