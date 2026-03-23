#include <stdio.h>

void main() {
	int math[5],i;
	double avg, sum;
	for(i=0;i<5;i++){
		printf("%d번째 학생의 수학점수를 입력하시오:",i+1);
		scanf("%d", &math[i]);
	}
	sum = 0;
	for(i=0;i<5;i++){
		sum += math[i];
	}
	avg = sum/i;
	printf("평균 성적:%lf", avg);
}
