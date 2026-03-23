#include <stdio.h>

double avg(double a, double b, double c){
	double res;
	res = (a+b+c)/3;
	return res;
}

void main() {
	double num1, num2, num3, result;
	printf("숫자 세 개를 입력하시오:");
	scanf("%lf %lf %lf", &num1,&num2,&num3);
	result = avg(num1,num2,num3);
	printf("평균:%lf", result);
	
	
}
