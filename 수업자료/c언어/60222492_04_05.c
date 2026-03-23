#include <stdio.h>
void main(){
	int k,e,m,sum;
	double eve;
	printf("국어점수를 입력하시오:");
	scanf("%d",&k);
	printf("영어점수를 입력하시오:");
	scanf("%d",&e);
	printf("수학점수를 입력하시오:");
	scanf("%d",&m);
	sum = k+e+m;
	eve = (k+e+m)/3.0;
	printf("당신의 총합점수는 %d점,평균은 %lf점입니다",sum,eve);
}
