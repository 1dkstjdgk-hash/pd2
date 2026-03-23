#include <stdio.h>
void main(){
	int num;
	printf("사각형(1), 삼각형(2), 원(3)중 하나를 입력하시오:");
	scanf("%d",&num);
	switch(num){
		case 1:printf("Rectangle");
		       break;
		case 2:printf("Triangle");
		       break;
		case 3:printf("Circle");
		       break;
		default:printf("Unknown");        
	}
	
	
}
