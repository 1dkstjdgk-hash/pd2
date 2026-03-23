#include <stdio.h>
#include <stdlib.h>
#include <time.h>

void main() {
	int dice[6],i;
	srand((unsigned)time(NULL));
	for(i=0;i<6;i++){
		dice[i]= 2 + (rand()%6) + (rand()%6);
	}
	for(i=0;i<6;i += 2){
			printf("%d번째 주사위 숫자:%d\n",i+1,dice[i]);
	}
}

