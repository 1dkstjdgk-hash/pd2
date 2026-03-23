#include <stdio.h>
void main(){
	
	int num1,num2,bsum,bbsum;
	printf("정수 두 개를 입력하시오:");
	scanf("%d %d",&num1,&num2);
	bsum = num1|num2;
	bbsum = num1^num2;
	printf("두 정수의 비트 논리합 결과는 %d입니다.\n",bsum);
	printf("두 정수의 비트 배타적 논리합 결과는 %d입니다.",bbsum);
}
