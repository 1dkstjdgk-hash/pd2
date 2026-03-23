#include <stdio.h>

void main() {
	int num[6], i;
	for(i=0;i<6;i++){
		printf("%d번째 정수를 입력하시오:",i+1);
		scanf("%d", &num[i]);
	}
	for(i=0;i<6;i++){
		if((i+1) % 2 == 1)
			printf("%d번째 입력된 수:%d\n", i+1,num[i]);
	}
}
