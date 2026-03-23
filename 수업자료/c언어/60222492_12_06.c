#include <stdio.h>
#include <stdlib.h>
#include <time.h>
void main() {
	srand((unsigned)time(NULL));
	int dice,sum = 0,i;
	for(i=0;i<10;i++){
		dice = 2 +(rand()%6)+(rand()%6);
		printf("두개의 주사위의 합:%d\n", dice);
		sum += dice;
	}
	printf("10번 굴린 주사위 눈금의 총합:%d",sum);
}
