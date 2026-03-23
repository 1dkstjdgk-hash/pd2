#include <stdio.h>
#define PI 3.14
void main(){
	double radius,area;
	printf("반지름을 입력하시오:");
	scanf("%lf",&radius);
	area = radius*radius*PI;
	printf("원의 넓이는 %lf입니다.",area);
}
