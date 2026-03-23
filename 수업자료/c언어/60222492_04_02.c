#include <stdio.h>
void main(){
	int k,eng,math,e;
	printf("국어점수를 입력하시오:");
	scanf("%d",&k);
	printf("영어점수를 입력하시오:");
	scanf("%d",&eng);
	printf("수학점수를 입력하시오:");
	scanf("%d",&math);
	e =(k+eng+math);
	printf("당신의 점수 총합은%d입니다.",e);
}
