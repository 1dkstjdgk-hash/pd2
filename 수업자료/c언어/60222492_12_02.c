#include <stdio.h>
#include <math.h>
void samgak(double a){
	double rad, si, co, ta;
	rad = (3.141592 * a) / 180;
	si = sin(rad);
	co = cos(rad);
	ta = tan(rad);
	printf("입력한 각도의 sin값: %lf\n", si);
	printf("입력한 각도의 cosin값: %lf\n", co);
	printf("입력한 각도의 tangent값: %lf\n", ta);
}

void main() {
	double angle;
	printf("각도를 입력하시오: ");
	scanf("%lf", &angle);
	samgak(angle);
	
	
}
