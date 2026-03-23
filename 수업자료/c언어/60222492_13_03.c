#include <stdio.h>

void main() {
	int math[5], max,i;
	for(i=0;i<5;i++){
		printf("%d번째 학생의 수학 점수를 입력하시오:", i+1);
		scanf("%d", &math[i]);
	}
	max = math[0];
	for(i=1; i<5;i++){
		if(math[i]>max)
			max = math[i];
	}
	printf("최고 점수:%d", max);
}
