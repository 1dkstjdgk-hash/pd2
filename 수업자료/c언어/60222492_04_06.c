#include <stdio.h>
#define PI 3.141592
void main(){
	double r,h,v;
	
	printf("원뿔의 반지름과 높이를 입력하시오:");
	scanf("%lf %lf",&r,&h);
	
	v = (1/3.0)*PI*r*r*h;
	printf("원뿔의 부피는%lf입니다.",v);
}
