#include <stdio.h>
#include <stdlib.h>
#include <time.h>
int num,i,dice1,dice2;

num = 0;
srand((unsigned) time(NULL))
for(i=0;i<100;i++){
	
	dice1[i]= 1+rand()%6;
	dice2[i]= 1+rand()%6;
	if(dice1[i]%2==0&&dice2[i]%2==0){
		num++;
	}
	printf("µ¿½Ã¿¡ Â¦¼ö°¡ ³ª¿Â È½¼ö:%d",num);
	
}


