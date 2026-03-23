#include <stdio.h>
#include <math.h>

void suhak(double x, double y){
	printf("x의 y제곱:%lf\n",pow(x,y));
	printf("루트x:%lf\n",sqrt(x));
	printf("루트y:%lf\n",sqrt(y));
}

void main() {
	int num1,num2;
	printf("실수 x와 y를 입력하시오:");
	scanf("%d %d", &num1,&num2);
	suhak(num1,num2);
}
